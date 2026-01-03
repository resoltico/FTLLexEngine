---
afad: "3.1"
version: "0.51.0"
domain: RUNTIME
updated: "2026-01-03"
route:
  keywords: [number_format, datetime_format, currency_format, FluentResolver, FluentNumber, formatting, locale]
  questions: ["how to format numbers?", "how to format dates?", "how to format currency?", "what is FluentNumber?"]
---

# Runtime Reference

---

## `FluentNumber`

Wrapper preserving numeric identity through NUMBER() formatting.

### Signature
```python
@dataclass(frozen=True, slots=True)
class FluentNumber:
    value: int | float | Decimal
    formatted: str
```

### Parameters
| Field | Type | Req | Description |
|:------|:-----|:----|:------------|
| `value` | `int \| float \| Decimal` | Y | Original numeric value for plural matching. |
| `formatted` | `str` | Y | Locale-formatted string for display. |

### Constraints
- Return: Frozen dataclass instance.
- State: Immutable. Safe for caching.
- Thread: Safe.
- Usage: Returned by `number_format()`. Preserves numeric identity for select expressions.
- Str: `str(fluent_number)` returns `formatted` for display.
- Import: `from ftllexengine.runtime.function_bridge import FluentNumber`

---

## `number_format`

### Signature
```python
def number_format(
    value: int | float | Decimal,
    locale_code: str = "en-US",
    *,
    minimum_fraction_digits: int = 0,
    maximum_fraction_digits: int = 3,
    use_grouping: bool = True,
    pattern: str | None = None,
) -> FluentNumber:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `value` | `int \| float \| Decimal` | Y | Number to format. |
| `locale_code` | `str` | N | BCP 47 locale code. |
| `minimum_fraction_digits` | `int` | N | Minimum decimal places. |
| `maximum_fraction_digits` | `int` | N | Maximum decimal places. |
| `use_grouping` | `bool` | N | Use thousands separator. |
| `pattern` | `str \| None` | N | Custom Babel number pattern. |

### Constraints
- Return: `FluentNumber` with formatted string and original numeric value.
- Raises: `FormattingError` on formatting failure (invalid pattern, Babel error).
- State: None.
- Thread: Safe.
- Plural: Original value preserved for correct plural category matching in select expressions.

---

## `datetime_format`

### Signature
```python
def datetime_format(
    value: datetime | str,
    locale_code: str = "en-US",
    *,
    date_style: Literal["short", "medium", "long", "full"] = "medium",
    time_style: Literal["short", "medium", "long", "full"] | None = None,
    pattern: str | None = None,
) -> str:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `value` | `datetime \| str` | Y | Datetime or ISO string. |
| `locale_code` | `str` | N | BCP 47 locale code. |
| `date_style` | `Literal[...]` | N | Date format style. |
| `time_style` | `Literal[...] \| None` | N | Time format style. |
| `pattern` | `str \| None` | N | Custom Babel datetime pattern. |

### Constraints
- Return: Formatted datetime string.
- Raises: `FormattingError` on invalid input (invalid ISO string, Babel failure).
- State: None.
- Thread: Safe.

---

## `currency_format`

### Signature
```python
def currency_format(
    value: int | float | Decimal,
    locale_code: str = "en-US",
    *,
    currency: str,
    currency_display: Literal["symbol", "code", "name"] = "symbol",
    pattern: str | None = None,
) -> str:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `value` | `int \| float \| Decimal` | Y | Monetary amount. |
| `locale_code` | `str` | N | BCP 47 locale code. |
| `currency` | `str` | Y | ISO 4217 currency code. |
| `currency_display` | `Literal[...]` | N | Display style. |
| `pattern` | `str \| None` | N | Custom CLDR currency pattern. |

### Constraints
- Return: Formatted currency string.
- Raises: `FormattingError` on formatting failure (invalid currency code, Babel error).
- State: None.
- Thread: Safe.

---

## `FunctionSignature`

### Signature
```python
@dataclass(frozen=True, slots=True)
class FunctionSignature:
    python_name: str
    ftl_name: str
    param_mapping: tuple[tuple[str, str], ...]
    callable: Callable[..., FluentValue]
```

### Parameters
| Field | Type | Description |
|:------|:-----|:------------|
| `python_name` | `str` | Python function name (snake_case). |
| `ftl_name` | `str` | FTL function name (UPPERCASE). |
| `param_mapping` | `tuple[tuple[str, str], ...]` | Immutable mapping of FTL camelCase to Python snake_case params. |
| `callable` | `Callable[..., FluentValue]` | The registered Python function. |

### Constraints
- Return: Frozen dataclass instance.
- State: Fully immutable. param_mapping uses tuple for safe sharing across registries.
- Thread: Safe for reads.

---

## `FunctionRegistry`

### Signature
```python
class FunctionRegistry:
    __slots__ = ("_frozen", "_functions")

    def __init__(self) -> None: ...
    def register(
        self,
        func: Callable[..., FluentValue],
        *,
        ftl_name: str | None = None
    ) -> None: ...
    def call(
        self,
        ftl_name: str,
        positional: Sequence[FluentValue],
        named: Mapping[str, FluentValue],
    ) -> FluentValue: ...
    def has_function(self, ftl_name: str) -> bool: ...
    def freeze(self) -> None: ...
    @property
    def frozen(self) -> bool: ...
    def get_callable(self, ftl_name: str) -> Callable[..., FluentValue] | None: ...
    def get_function_info(self, ftl_name: str) -> FunctionSignature | None: ...
    def get_python_name(self, ftl_name: str) -> str | None: ...
    def list_functions(self) -> list[str]: ...
    def copy(self) -> FunctionRegistry: ...
    def __iter__(self) -> Iterator[str]: ...
    def __len__(self) -> int: ...
    def __contains__(self, ftl_name: str) -> bool: ...
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|

### Constraints
- Return: Registry instance.
- State: Mutable until frozen. Shared registry is frozen after creation.
- Thread: Unsafe for concurrent register(). Safe for reads after freeze().
- Memory: Uses __slots__ for reduced memory footprint.
- Freeze: Once frozen, register() raises TypeError. Use copy() for mutable clone.

---

## `FunctionRegistry.get_callable`

### Signature
```python
def get_callable(self, ftl_name: str) -> Callable[..., FluentValue] | None:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `ftl_name` | `str` | Y | FTL function name (e.g., "NUMBER"). |

### Constraints
- Return: Registered callable, or None if not found.
- State: Read-only access.
- Thread: Safe for reads.

---

## `FunctionRegistry.call`

### Signature
```python
def call(
    self,
    ftl_name: str,
    positional: Sequence[FluentValue],
    named: Mapping[str, FluentValue],
) -> FluentValue:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `ftl_name` | `str` | Y | Function name from FTL (e.g., "NUMBER"). |
| `positional` | `Sequence[FluentValue]` | Y | Positional arguments. |
| `named` | `Mapping[str, FluentValue]` | Y | Named arguments from FTL (camelCase). |

### Constraints
- Return: Function result as FluentValue.
- Raises: FluentReferenceError if function not found.
- Raises: FluentResolutionError if function execution fails.
- State: Read-only access to registry.
- Thread: Safe for calls.

---

## `FunctionRegistry.register`

### Signature
```python
def register(
    self,
    func: Callable[..., FluentValue],
    *,
    ftl_name: str | None = None,
    param_map: dict[str, str] | None = None,
) -> None:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `func` | `Callable[..., FluentValue]` | Y | Function to register. |
| `ftl_name` | `str \| None` | N | FTL name override (default: UPPERCASE of func name). |
| `param_map` | `dict[str, str] \| None` | N | Custom parameter mappings (overrides auto-generation). |

### Constraints
- Return: None.
- Raises: `TypeError` if registry is frozen (via `freeze()` method).
- Raises: `ValueError` if parameter names collide after underscore stripping (e.g., `_value` and `value`).
- State: Mutates registry.
- Thread: Unsafe.

---

## `create_default_registry`

### Signature
```python
def create_default_registry() -> FunctionRegistry:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|

### Constraints
- Return: Fresh FunctionRegistry with NUMBER, DATETIME, CURRENCY registered.
- Raises: Never.
- State: Returns new isolated instance each call.
- Thread: Safe.
- Import: `from ftllexengine.runtime.functions import create_default_registry`

---

## `get_shared_registry`

### Signature
```python
def get_shared_registry() -> FunctionRegistry:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|

### Constraints
- Return: Frozen FunctionRegistry singleton with NUMBER, DATETIME, CURRENCY.
- Raises: Never.
- State: Returns shared frozen singleton (lazy initialized). Calling `register()` raises `TypeError`.
- Thread: Safe for reads. Use `copy()` to get mutable registry for customization.
- Performance: Avoids repeated registry creation for multi-bundle applications.
- Import: `from ftllexengine.runtime.functions import get_shared_registry`

---

## `FunctionCategory`

### Signature
```python
class FunctionCategory(StrEnum):
    FORMATTING = "formatting"
    TEXT = "text"
    CUSTOM = "custom"
```

### Parameters
| Value | Description |
|:------|:------------|
| `FORMATTING` | Number, date, currency formatting functions. |
| `TEXT` | Text manipulation functions. |
| `CUSTOM` | User-defined functions. |

### Constraints
- StrEnum: Members ARE strings. `str(FunctionCategory.FORMATTING) == "formatting"`
- Import: `from ftllexengine.runtime.function_metadata import FunctionCategory`

---

## `FunctionMetadata`

### Signature
```python
@dataclass(frozen=True, slots=True)
class FunctionMetadata:
    python_name: str
    ftl_name: str
    requires_locale: bool
    expected_positional_args: int = 1
    category: FunctionCategory = FunctionCategory.FORMATTING
```

### Parameters
| Field | Type | Req | Description |
|:------|:-----|:----|:------------|
| `python_name` | `str` | Y | Python function name (snake_case). |
| `ftl_name` | `str` | Y | FTL function name (UPPERCASE). |
| `requires_locale` | `bool` | Y | Whether function needs bundle locale injected. |
| `expected_positional_args` | `int` | N | Expected positional args from FTL (before locale). |
| `category` | `FunctionCategory` | N | Function category for documentation. |

### Constraints
- Immutable: Frozen dataclass with slots.
- Thread: Safe.
- Import: `from ftllexengine.runtime.function_metadata import FunctionMetadata`

---

## `BUILTIN_FUNCTIONS`

### Signature
```python
BUILTIN_FUNCTIONS: dict[str, FunctionMetadata] = {
    "NUMBER": FunctionMetadata(...),
    "DATETIME": FunctionMetadata(...),
    "CURRENCY": FunctionMetadata(...),
}
```

### Constraints
- Type: `dict[str, FunctionMetadata]`
- Contents: Metadata for NUMBER, DATETIME, CURRENCY.
- Read-only: Do not modify at runtime.
- Import: `from ftllexengine.runtime.function_metadata import BUILTIN_FUNCTIONS`

---

## `is_builtin_with_locale_requirement`

### Signature
```python
def is_builtin_with_locale_requirement(func: object) -> bool:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `func` | `object` | Y | Callable to check. |

### Constraints
- Return: True if func has `_ftl_requires_locale = True`.
- Thread: Safe.
- Import: `from ftllexengine.runtime.functions import is_builtin_with_locale_requirement`

---

## `get_expected_positional_args`

### Signature
```python
def get_expected_positional_args(ftl_name: str) -> int | None:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `ftl_name` | `str` | Y | FTL function name (e.g., "NUMBER"). |

### Constraints
- Return: Expected positional arg count, or None if not built-in.
- Thread: Safe.
- Import: `from ftllexengine.runtime.function_metadata import get_expected_positional_args`

---

## `FunctionRegistry.should_inject_locale`

### Signature
```python
def should_inject_locale(self, ftl_name: str) -> bool:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `ftl_name` | `str` | Y | FTL function name. |

### Constraints
- Return: True if locale should be injected for this call.
- Logic: Checks callable's `_ftl_requires_locale` attribute set by `@fluent_function(inject_locale=True)`.
- Thread: Safe.
- Access: Via `bundle._function_registry.should_inject_locale(name)` or registry instance.

---

## `fluent_function`

### Signature
```python
@overload
def fluent_function[F: Callable[..., FluentValue]](func: F, *, inject_locale: bool = False) -> F: ...
@overload
def fluent_function[F: Callable[..., FluentValue]](func: None = None, *, inject_locale: bool = False) -> Callable[[F], F]: ...
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `func` | `F \| None` | N | Function to decorate. |
| `inject_locale` | `bool` | N | If True, inject bundle locale as second argument. |

### Constraints
- Return: Decorated function with Fluent metadata attributes.
- Thread: Safe.
- Import: `from ftllexengine import fluent_function`

---

## `select_plural_category`

### Signature
```python
def select_plural_category(n: int | float | Decimal, locale: str) -> str:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `n` | `int \| float \| Decimal` | Y | Number to categorize. |
| `locale` | `str` | Y | BCP 47 locale code. |

### Constraints
- Return: CLDR plural category (zero, one, two, few, many, other).
- Raises: Never. Returns "one" or "other" on invalid locale.
- State: None.
- Thread: Safe.

---

## FTL Function Name Mapping

| FTL Name | Python Function | Parameter Mapping |
|:---------|:----------------|:------------------|
| `NUMBER` | `number_format` | minimumFractionDigits -> minimum_fraction_digits |
| `DATETIME` | `datetime_format` | dateStyle -> date_style, timeStyle -> time_style |
| `CURRENCY` | `currency_format` | currencyDisplay -> currency_display |

---

## Custom Function Protocol

### Signature
```python
def CUSTOM_FUNCTION(
    positional_arg: FluentValue,
    locale_code: str,
    /,
    *,
    keyword_arg: str = "default",
) -> FluentValue:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| First positional | `FluentValue` | Y | Primary input value. |
| `locale_code` | `str` | Y | Locale code (positional-only). |
| Keyword args | `FluentValue` | N | Named options. |

### Constraints
- Return: FluentValue (typically str; non-string values converted by resolver).
- Raises: Should not raise. Return fallback on error.
- State: Should be stateless.
- Thread: Should be safe.

---

## `validate_resource`

### Signature
```python
def validate_resource(
    source: str,
    *,
    parser: FluentParserV1 | None = None,
    known_messages: frozenset[str] | None = None,
    known_terms: frozenset[str] | None = None,
) -> ValidationResult:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `source` | `str` | Y | FTL file content. |
| `parser` | `FluentParserV1 \| None` | N | Parser instance (creates default if not provided). |
| `known_messages` | `frozenset[str] \| None` | N | Message IDs from other resources (cross-resource validation). |
| `known_terms` | `frozenset[str] \| None` | N | Term IDs from other resources (cross-resource validation). |

### Constraints
- Return: ValidationResult with errors, warnings, and semantic annotations.
- Validation Passes: (1) Syntax errors, (2) Structural issues, (3) Undefined refs, (4) Cycles, (5) Semantic (Fluent spec E0001-E0013).
- Cross-Resource: References to `known_messages`/`known_terms` do not produce undefined warnings.
- Raises: Never. Critical parse errors returned as ValidationError.
- State: None (creates isolated parser if not provided).
- Thread: Safe.
- Import: `from ftllexengine.validation import validate_resource`

---

## `ResolutionContext`

### Signature
```python
@dataclass(slots=True)
class ResolutionContext:
    stack: list[str] = field(default_factory=list)
    _seen: set[str] = field(default_factory=set)
    max_depth: int = MAX_DEPTH
    max_expression_depth: int = MAX_DEPTH
    _expression_guard: DepthGuard = field(init=False)

    def __post_init__(self) -> None: ...
    def push(self, key: str) -> None: ...
    def pop(self) -> str: ...
    def contains(self, key: str) -> bool: ...
    @property
    def expression_guard(self) -> DepthGuard: ...
    @property
    def expression_depth(self) -> int: ...
    @property
    def depth(self) -> int: ...
    def is_depth_exceeded(self) -> bool: ...
    def get_cycle_path(self, key: str) -> list[str]: ...
```

### Parameters
| Field | Type | Description |
|:------|:-----|:------------|
| `stack` | `list[str]` | Resolution stack for cycle path. |
| `_seen` | `set[str]` | O(1) membership check set. |
| `max_depth` | `int` | Maximum resolution depth (default: MAX_DEPTH=100). |
| `max_expression_depth` | `int` | Maximum expression depth (default: MAX_DEPTH=100). |
| `_expression_guard` | `DepthGuard` | Internal depth guard (init=False). |

### Constraints
- Thread: Safe (explicit parameter passing, no global state).
- Purpose: Replaces thread-local state for async/concurrent compatibility.
- Complexity: contains() is O(1) via _seen set.
- Import: `from ftllexengine.runtime import ResolutionContext`
- Constants: `MAX_DEPTH` from `ftllexengine.constants`

---

## `ResolutionContext.push`

### Signature
```python
def push(self, key: str) -> None:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `key` | `str` | Y | Message key to push onto stack. |

### Constraints
- Return: None.
- State: Mutates stack.

---

## `ResolutionContext.pop`

### Signature
```python
def pop(self) -> str:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|

### Constraints
- Return: Removed message key.
- Raises: IndexError if stack empty.
- State: Mutates stack.

---

## `ResolutionContext.contains`

### Signature
```python
def contains(self, key: str) -> bool:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `key` | `str` | Y | Message key to check. |

### Constraints
- Return: True if key is in resolution stack (cycle detected).
- Complexity: O(1) via _seen set lookup.
- State: Read-only.

---

## `ResolutionContext.expression_guard`

### Signature
```python
@property
def expression_guard(self) -> DepthGuard:
```

### Constraints
- Return: DepthGuard for expression depth tracking.
- Usage: Use as context manager (`with context.expression_guard:`).
- Raises: DepthLimitExceededError when depth limit exceeded.
- State: Read-only property returning internal DepthGuard.

---

## `ResolutionContext.expression_depth`

### Signature
```python
@property
def expression_depth(self) -> int:
```

### Constraints
- Return: Current expression nesting depth.
- State: Read-only property (delegates to expression_guard.current_depth).

---

## `ResolutionContext.depth`

### Signature
```python
@property
def depth(self) -> int:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|

### Constraints
- Return: Current resolution depth (stack length).
- State: Read-only.

---

## `ResolutionContext.is_depth_exceeded`

### Signature
```python
def is_depth_exceeded(self) -> bool:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|

### Constraints
- Return: True if depth >= max_depth.
- State: Read-only.

---

## `ResolutionContext.get_cycle_path`

### Signature
```python
def get_cycle_path(self, key: str) -> list[str]:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `key` | `str` | Y | Message key that caused cycle. |

### Constraints
- Return: List of keys showing cycle path including triggering key.
- State: Read-only.

---

## `FluentResolver`

### Signature
```python
class FluentResolver:
    __slots__ = ("function_registry", "locale", "messages", "terms", "use_isolating")

    def __init__(
        self,
        locale: str,
        messages: dict[str, Message],
        terms: dict[str, Term],
        *,
        function_registry: FunctionRegistry,
        use_isolating: bool = True,
    ) -> None: ...

    def resolve_message(
        self,
        message: Message,
        args: Mapping[str, FluentValue] | None = None,
        attribute: str | None = None,
        *,
        context: ResolutionContext | None = None,
    ) -> tuple[str, tuple[FluentError, ...]]: ...
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `locale` | `str` | Y | Locale code for plural selection. |
| `messages` | `dict[str, Message]` | Y | Message registry. |
| `terms` | `dict[str, Term]` | Y | Term registry. |
| `function_registry` | `FunctionRegistry` | Y | Function registry. |
| `use_isolating` | `bool` | N | Wrap values in Unicode bidi marks. |

### Constraints
- Return: Resolver instance.
- State: Immutable after construction.
- Thread: Safe (uses explicit context).
- Import: `from ftllexengine.runtime import FluentResolver`

---

## `FluentResolver.resolve_message`

### Signature
```python
def resolve_message(
    self,
    message: Message,
    args: Mapping[str, FluentValue] | None = None,
    attribute: str | None = None,
    *,
    context: ResolutionContext | None = None,
) -> tuple[str, tuple[FluentError, ...]]:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `message` | `Message` | Y | Message AST. |
| `args` | `Mapping[str, FluentValue] \| None` | N | Variable arguments. |
| `attribute` | `str \| None` | N | Attribute name to resolve. |
| `context` | `ResolutionContext \| None` | N | Resolution context (creates fresh if None). |

### Constraints
- Return: Tuple of (formatted_string, errors).
- Raises: Never. Collects errors in tuple.
- State: Read-only.
- Thread: Safe.

---

## Module Constants

### `DEFAULT_CACHE_SIZE`

```python
DEFAULT_CACHE_SIZE: int = 1000
```

| Attribute | Value |
|:----------|:------|
| Type | `int` |
| Value | 1000 |
| Location | `ftllexengine.constants` |

- Purpose: Default maximum cache entries for FluentBundle format results.
- Usage: Referenced by `FluentBundle.__init__`, `create()`, `for_system_locale()`.
- Import: `from ftllexengine.constants import DEFAULT_CACHE_SIZE`

---

### `UNICODE_FSI` / `UNICODE_PDI`

```python
UNICODE_FSI: str = "\u2068"  # U+2068 FIRST STRONG ISOLATE
UNICODE_PDI: str = "\u2069"  # U+2069 POP DIRECTIONAL ISOLATE
```

| Attribute | Value |
|:----------|:------|
| Type | `str` |
| Location | `ftllexengine.runtime.resolver` |

- Purpose: Unicode bidirectional isolation characters per Unicode TR9.
- Usage: Wraps interpolated values when `use_isolating=True`.

---

### `MAX_DEPTH`

```python
MAX_DEPTH: int = 100
```

| Attribute | Value |
|:----------|:------|
| Type | `int` |
| Value | 100 |
| Location | `ftllexengine.constants` |
| Re-exported | `ftllexengine.core.depth_guard` |

- Purpose: Unified maximum depth for all recursion protection.
- Usage: Message reference chains, expression nesting, serialization, validation.
- Import: `from ftllexengine.constants import MAX_DEPTH`

---

## `DepthGuard`

### Signature
```python
@dataclass(slots=True)
class DepthGuard:
    max_depth: int = MAX_DEPTH
    current_depth: int = field(default=0, init=False)

    def __enter__(self) -> DepthGuard: ...
    def __exit__(self, exc_type, exc_val, exc_tb) -> None: ...
    @property
    def depth(self) -> int: ...
    def is_exceeded(self) -> bool: ...
    def check(self) -> None: ...
    def increment(self) -> None: ...
    def decrement(self) -> None: ...
    def reset(self) -> None: ...
```

### Parameters
| Field | Type | Description |
|:------|:-----|:------------|
| `max_depth` | `int` | Maximum allowed depth. |
| `current_depth` | `int` | Current recursion depth. |

### Constraints
- Thread: Safe (explicit instance state, reentrant).
- Usage: Context manager or manual increment/decrement.
- Raises: DepthLimitExceededError when depth limit exceeded.
- Behavior: `__enter__` validates limit BEFORE incrementing; prevents state corruption on exception.
- Import: `from ftllexengine.core.depth_guard import DepthGuard`

---
