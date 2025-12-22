---
spec_version: AFAD-v1
project_version: 0.28.0
context: CORE
last_updated: 2025-12-21T00:00:00Z
maintainer: claude-opus-4-5
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
    ) -> None: ...
```

### Contract
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `locale` | `str` | Y | BCP 47 locale code (positional-only). |
| `use_isolating` | `bool` | N | Wrap interpolated values in Unicode bidi marks. |
| `enable_cache` | `bool` | N | Enable format result caching. |
| `cache_size` | `int` | N | Maximum cache entries. |
| `functions` | `FunctionRegistry \| None` | N | Custom function registry (v0.18.0+). |

### Constraints
- Return: FluentBundle instance.
- Raises: `ValueError` on invalid locale format.
- State: Creates internal message/term registries.
- Thread: Unsafe for writes, safe for reads after initialization.
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
) -> FluentBundle:
```

### Contract
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `use_isolating` | `bool` | N | Wrap interpolated values in Unicode bidi marks. |
| `enable_cache` | `bool` | N | Enable format result caching. |
| `cache_size` | `int` | N | Maximum cache entries. |
| `functions` | `FunctionRegistry \| None` | N | Custom function registry (v0.18.0+). |

### Constraints
- Return: FluentBundle with system locale.
- Raises: `RuntimeError` if locale cannot be determined.
- State: Detects locale from LC_ALL, LC_MESSAGES, LANG.
- Thread: Safe.

---

## `FluentBundle.__enter__`

### Signature
```python
def __enter__(self) -> FluentBundle:
```

### Contract
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
    exc_tb: TracebackType | None,
) -> None:
```

### Contract
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `exc_type` | `type[BaseException] \| None` | N | Exception type. |
| `exc_val` | `BaseException \| None` | N | Exception value. |
| `exc_tb` | `TracebackType \| None` | N | Traceback object. |

### Constraints
- Return: None (does not suppress exceptions).
- Raises: None.
- State: Clears format cache on context exit.
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
) -> None:
```

### Contract
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `source` | `str` | Y | FTL source code (positional-only). |
| `source_path` | `str \| None` | N | Path for error messages. |

### Constraints
- Return: None.
- Raises: `FluentSyntaxError` on critical parse error.
- State: Mutates internal message/term registries. Clears cache.
- Thread: Unsafe.

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

### Contract
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

### Contract
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

### Contract
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `source` | `str` | Y | FTL source code to validate. |

### Constraints
- Return: ValidationResult with errors and warnings.
- Raises: Never.
- State: None. Does not modify bundle.
- Thread: Safe.

---

## `FluentBundle.has_message`

### Signature
```python
def has_message(self, message_id: str) -> bool:
```

### Contract
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `message_id` | `str` | Y | Message identifier to check. |

### Constraints
- Return: True if message exists.
- Raises: None.
- State: Read-only.
- Thread: Safe.

---

## `FluentBundle.get_message_ids`

### Signature
```python
def get_message_ids(self) -> list[str]:
```

### Contract
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

### Contract
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

### Contract
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

### Contract
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `message_id` | `str` | Y | Message identifier. |

### Constraints
- Return: MessageIntrospection with complete metadata.
- Raises: `KeyError` if message not found.
- State: Read-only.
- Thread: Safe.

---

## `FluentBundle.add_function`

### Signature
```python
def add_function(self, name: str, func: Callable[..., str]) -> None:
```

### Contract
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `name` | `str` | Y | Function name (UPPERCASE convention). |
| `func` | `Callable[..., str]` | Y | Python function returning string. |

### Constraints
- Return: None.
- Raises: None.
- State: Mutates function registry. Clears cache.
- Thread: Unsafe.

---

## `FluentBundle.clear_cache`

### Signature
```python
def clear_cache(self) -> None:
```

### Contract
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
def get_cache_stats(self) -> dict[str, int] | None:
```

### Contract
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|

### Constraints
- Return: Dict with size/hits/misses/hit_rate, or None if disabled.
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

### Contract
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

### Contract
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

### Contract
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
- Return: Maximum cache entries (0 if caching disabled).
- Raises: None.
- State: Read-only property.
- Thread: Safe.

---

## `FluentBundle.get_babel_locale`

### Signature
```python
def get_babel_locale(self) -> str:
```

### Contract
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
    ) -> None: ...
```

### Contract
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `locales` | `Iterable[LocaleCode]` | Y | Locale codes in fallback order. |
| `resource_ids` | `Iterable[ResourceId] \| None` | N | FTL files to auto-load. |
| `resource_loader` | `ResourceLoader \| None` | N | Loader for FTL files. |
| `use_isolating` | `bool` | N | Wrap interpolated values in bidi marks. |
| `enable_cache` | `bool` | N | Enable format caching. |
| `cache_size` | `int` | N | Max cache entries per bundle. |

### Constraints
- Return: FluentLocalization instance.
- Raises: `ValueError` if locales empty or resource_ids without loader.
- State: Creates bundles for each locale.
- Thread: Unsafe for writes, safe for reads.

---

## `FluentLocalization.add_resource`

### Signature
```python
def add_resource(self, locale: LocaleCode, ftl_source: FTLSource) -> None:
```

### Contract
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `locale` | `LocaleCode` | Y | Target locale (must be in chain). |
| `ftl_source` | `FTLSource` | Y | FTL source code. |

### Constraints
- Return: None.
- Raises: `ValueError` if locale not in fallback chain.
- State: Mutates target bundle.
- Thread: Unsafe.

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

### Contract
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

### Contract
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

### Contract
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
def add_function(self, name: str, func: Callable[..., str]) -> None:
```

### Contract
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `name` | `str` | Y | Function name. |
| `func` | `Callable[..., str]` | Y | Python function. |

### Constraints
- Return: None.
- Raises: None.
- State: Mutates all bundles.
- Thread: Unsafe.

---

## `FluentLocalization.get_bundles`

### Signature
```python
def get_bundles(self) -> Generator[FluentBundle]:
```

### Contract
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
- Return: Maximum cache entries per bundle (0 if caching disabled).
- Raises: None.
- State: Read-only property.
- Thread: Safe.

---

## `FluentLocalization.get_babel_locale`

### Signature
```python
def get_babel_locale(self) -> str:
```

### Contract
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

### Contract
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

### Contract
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

### Contract
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

### Contract
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `base_path` | `str` | Y | Path template with {locale} placeholder. |
| `root_dir` | `str \| None` | N | Fixed root directory for path traversal validation. |

### Constraints
- Return: FTL source string from file.
- Raises: `FileNotFoundError` if file missing, `OSError` on read error, `ValueError` on path traversal attempt.
- State: None. Immutable dataclass.
- Thread: Safe.
- Security (v0.27.0+):
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

### Contract
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
