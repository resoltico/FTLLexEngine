---
afad: "3.3"
version: "0.133.0"
domain: RUNTIME
updated: "2026-02-25"
route:
  keywords: [number_format, datetime_format, currency_format, FluentResolver, FluentNumber, formatting, locale, RWLock, timeout, IntegrityCache, CacheConfig, audit, NaN, idempotent_writes, content_hash, IntegrityCacheEntry, detect_cycles, entry_dependency_set, make_cycle_key]
  questions: ["how to format numbers?", "how to format dates?", "how to format currency?", "what is FluentNumber?", "what is RWLock?", "how to set RWLock timeout?", "what is IntegrityCache?", "how to enable cache audit?", "how does cache handle NaN?", "what is idempotent write?", "how does thundering herd work?", "how to detect dependency cycles?"]
---

# Runtime Reference

---

## `FluentNumber`

Wrapper preserving numeric identity and precision through NUMBER() formatting.

### Signature
```python
@dataclass(frozen=True, slots=True)
class FluentNumber:
    value: int | Decimal
    formatted: str
    precision: int | None = None
```

### Parameters
| Field | Type | Req | Description |
|:------|:-----|:----|:------------|
| `value` | `int \| Decimal` | Y | Original numeric value for plural matching. `bool` is rejected — use `int(b)` at call site. |
| `formatted` | `str` | Y | Locale-formatted string for display. |
| `precision` | `int \| None` | N | Visible fraction digit count (CLDR v operand). Must be >= 0 when set. None if not specified. |

### Constraints
- Return: Frozen dataclass instance.
- Raises: `TypeError` if `value` is `bool` (no numeric localization semantics). `ValueError` if `precision < 0` (CLDR v operand is always non-negative).
- State: Immutable. Safe for caching.
- Thread: Safe.
- Usage: Returned by `number_format()` and `currency_format()`. Preserves numeric identity and precision metadata for select expressions.
- Str: `str(fluent_number)` returns `formatted` for display.
- Plural: Precision affects CLDR plural category selection. For example, "1.00" with precision=2 selects "other" category (v=2), not "one" (v=0).
- Import: `from ftllexengine.runtime.value_types import FluentNumber`

---

## `number_format`

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
) -> FluentNumber:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `value` | `int \| Decimal` | Y | Number to format. |
| `locale_code` | `str` | N | BCP 47 locale code. |
| `minimum_fraction_digits` | `int` | N | Minimum decimal places. |
| `maximum_fraction_digits` | `int` | N | Maximum decimal places. |
| `use_grouping` | `bool` | N | Use thousands separator. |
| `pattern` | `str \| None` | N | Custom Babel number pattern. |

### Constraints
- Return: `FluentNumber` with formatted string, original numeric value, and precision metadata.
- Raises: Never. Invalid locales fall back to en_US with a logged warning.
- State: None.
- Thread: Safe.
- Plural: Original value and precision preserved for correct CLDR plural category matching in select expressions. Precision parameter affects plural category selection (e.g., "1.00" with minimum_fraction_digits=2 selects "other" category due to v=2, not "one").
- Bounds: Fraction digit parameters clamped to `MAX_FORMAT_DIGITS` (20). Values exceeding the limit are silently clamped.
- Rounding: Uses CLDR half-up rounding (2.5->3, 3.5->4). Matches Intl.NumberFormat behavior.

---

## `datetime_format`

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

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `value` | `date \| datetime \| str` | Y | Date, datetime, or ISO 8601 string. Plain `date` is promoted to midnight `datetime` when `time_style` or `pattern` is set. |
| `locale_code` | `str` | N | BCP 47 locale code. |
| `date_style` | `Literal[...]` | N | Date format style. |
| `time_style` | `Literal[...] \| None` | N | Time format style. |
| `pattern` | `str \| None` | N | Custom Babel datetime pattern. |

### Constraints
- Return: Formatted date/datetime string.
- Raises: `FrozenFluentError` (FORMATTING) for invalid ISO 8601 strings. Invalid locales fall back to en_US.
- State: None.
- Thread: Safe.

---

## `currency_format`

### Signature
```python
def currency_format(
    value: int | Decimal,
    locale_code: str = "en-US",
    *,
    currency: str,
    currency_display: Literal["symbol", "code", "name"] = "symbol",
    pattern: str | None = None,
) -> FluentNumber:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `value` | `int \| Decimal` | Y | Monetary amount. |
| `locale_code` | `str` | N | BCP 47 locale code. |
| `currency` | `str` | Y | ISO 4217 currency code. |
| `currency_display` | `Literal[...]` | N | Display style. |
| `pattern` | `str \| None` | N | Custom CLDR currency pattern. |

### Constraints
- Return: `FluentNumber` with formatted currency string and computed precision. Enables CURRENCY results as selectors in plural/select expressions.
- Raises: Never. Invalid locales fall back to en_US with a logged warning.
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
- Raises: `FrozenFluentError` (category=REFERENCE) if function not found.
- Raises: `FrozenFluentError` (category=RESOLUTION) if function execution fails.
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
- Raises: `TypeError` if registry is frozen (via `freeze()` method) or if function marked with `inject_locale=True` has incompatible signature (requires ≥2 positional parameters for value and locale_code).
- Raises: `ValueError` if parameter names collide after underscore stripping (e.g., `_value` and `value`).
- State: Mutates registry. Validates function signature at registration (fail-fast).
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

## `FunctionRegistry.get_expected_positional_args`

### Signature
```python
def get_expected_positional_args(self, ftl_name: str) -> int | None:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `ftl_name` | `str` | Y | FTL function name (e.g., "NUMBER"). |

### Constraints
- Return: Expected positional arg count from `BUILTIN_FUNCTIONS` metadata, or None if not built-in.
- Thread: Safe.
- Access: Via `bundle.function_registry.get_expected_positional_args(name)` or registry instance.

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
- Access: Via `bundle.function_registry.should_inject_locale(name)` or registry instance.

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

Function that selects the CLDR plural category for a number using Babel's CLDR data.

### Signature
```python
def select_plural_category(
    n: int | Decimal,
    locale: str,
    precision: int | None = None,
) -> str:
```

### Parameters
| Parameter | Type | Req | Semantics |
|:----------|:-----|:----|:----------|
| `n` | `int \| Decimal` | Y | Number to categorize |
| `locale` | `str` | Y | BCP-47 or POSIX locale code |
| `precision` | `int \| None` | N | Fraction digits for CLDR v operand |

### Constraints
- Return: CLDR plural category (`"zero"`, `"one"`, `"two"`, `"few"`, `"many"`, `"other"`).
- Raises: `BabelImportError` if Babel not installed. Returns `"other"` on invalid locale.
- State: Read-only.
- Thread: Safe.
- Rounding: Uses `ROUND_HALF_UP` when `precision` is set, matching `format_number()` rounding.

---

## FTL Function Name Mapping

| FTL Name | Python Function | Parameter Mapping |
|:---------|:----------------|:------------------|
| `NUMBER` | `number_format` | minimumFractionDigits -> minimum_fraction_digits |
| `DATETIME` | `datetime_format` | dateStyle -> date_style, timeStyle -> time_style |
| `CURRENCY` | `currency_format` | currencyDisplay -> currency_display |

---

## Custom Function Protocol

### Signature (without locale injection)
```python
def CUSTOM_FUNCTION(
    positional_arg: FluentValue,
    /,
    *,
    keyword_arg: str = "default",
) -> FluentValue:
```

### Signature (with locale injection via `@fluent_function(inject_locale=True)`)
```python
@fluent_function(inject_locale=True)
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
| `locale_code` | `str` | Opt | Locale code (positional-only). Only present when `@fluent_function(inject_locale=True)` is applied. |
| Keyword args | `FluentValue` | N | Named options. |

### Constraints
- Return: FluentValue (typically str; non-string values converted by resolver).
- Raises: Should not raise. Return fallback on error.
- State: Should be stateless.
- Thread: Should be safe.
- Locale: `locale_code` is NOT automatically injected. Use `@fluent_function(inject_locale=True)` to opt in. Without it, the function receives only the FTL positional arg and keyword args.

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
    known_msg_deps: Mapping[str, frozenset[str]] | None = None,
    known_term_deps: Mapping[str, frozenset[str]] | None = None,
) -> ValidationResult:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `source` | `str` | Y | FTL file content. |
| `parser` | `FluentParserV1 \| None` | N | Parser instance (creates default if not provided). |
| `known_messages` | `frozenset[str] \| None` | N | Message IDs from other resources (cross-resource validation). |
| `known_terms` | `frozenset[str] \| None` | N | Term IDs from other resources (cross-resource validation). |
| `known_msg_deps` | `Mapping[str, frozenset[str]] \| None` | N | Dependency graph for known messages (prefixed: "msg:name", "term:name"). |
| `known_term_deps` | `Mapping[str, frozenset[str]] \| None` | N | Dependency graph for known terms (prefixed: "msg:name", "term:name"). |

### Constraints
- Return: ValidationResult with errors, warnings, and semantic annotations.
- Validation Passes: (1) Syntax errors, (2) Structural issues + duplicate attributes + shadow conflicts, (3) Undefined refs, (4) Cycles (intra-resource and cross-resource), (5) Chain depth, (6) Semantic (Fluent spec E0001-E0013).
- Chain Depth: Warns if reference chains exceed MAX_DEPTH (would fail at runtime with MAX_DEPTH_EXCEEDED).
- Cross-Resource: References to `known_messages`/`known_terms` do not produce undefined warnings. Cycles detected across resource boundaries. Shadow warnings emitted when current resource redefines known entry.
- Duplicate Attributes: Emits VALIDATION_DUPLICATE_ATTRIBUTE (5107) for duplicate attribute IDs within entry.
- Shadow Warnings: Emits VALIDATION_SHADOW_WARNING (5108) when entry ID matches known bundle entry.
- Raises: `TypeError` if source is not a str.
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
    max_expansion_size: int = DEFAULT_MAX_EXPANSION_SIZE
    _total_chars: int = 0
    _expression_guard: DepthGuard = field(init=False)

    def __post_init__(self) -> None: ...
    def push(self, key: str) -> None: ...
    def pop(self) -> str: ...
    def contains(self, key: str) -> bool: ...
    def track_expansion(self, char_count: int) -> None: ...
    @property
    def total_chars(self) -> int: ...
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
| `max_expansion_size` | `int` | Maximum total output characters (default: 1,000,000). Prevents Billion Laughs. |
| `_total_chars` | `int` | Running character count (internal; use `total_chars` property). |
| `_expression_guard` | `DepthGuard` | Internal depth guard (init=False). |

### Constraints
- Thread: Safe (explicit parameter passing, no global state).
- Purpose: Replaces thread-local state for async/concurrent compatibility.
- Complexity: contains() is O(1) via _seen set.
- Expansion: track_expansion() raises EXPANSION_BUDGET_EXCEEDED when total_chars exceeds max_expansion_size.
- Import: `from ftllexengine.runtime import ResolutionContext`
- Constants: `MAX_DEPTH`, `DEFAULT_MAX_EXPANSION_SIZE` from `ftllexengine.constants`

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

## `ResolutionContext.total_chars`

### Signature
```python
@property
def total_chars(self) -> int:
```

### Constraints
- Return: Running count of resolved characters.
- State: Read-only property over internal `_total_chars`.
- Usage: Preferred over direct `_total_chars` access for encapsulation.

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
- Raises: `FrozenFluentError` (category=RESOLUTION) when depth limit exceeded.
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
    __slots__ = ("function_registry", "locale", "messages", "terms", "use_isolating", "_max_nesting_depth")

    def __init__(
        self,
        locale: str,
        messages: dict[str, Message],
        terms: dict[str, Term],
        *,
        function_registry: FunctionRegistry,
        use_isolating: bool = True,
        max_nesting_depth: int = 100,
    ) -> None: ...

    def resolve_message(
        self,
        message: Message,
        args: Mapping[str, FluentValue] | None = None,
        attribute: str | None = None,
        *,
        context: ResolutionContext | None = None,
    ) -> tuple[str, tuple[FrozenFluentError, ...]]: ...
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `locale` | `str` | Y | Locale code for plural selection. |
| `messages` | `dict[str, Message]` | Y | Message registry. |
| `terms` | `dict[str, Term]` | Y | Term registry. |
| `function_registry` | `FunctionRegistry` | Y | Function registry. |
| `use_isolating` | `bool` | N | Wrap values in Unicode bidi marks. |
| `max_nesting_depth` | `int` | N | Maximum resolution depth limit (default: 100). |

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
) -> tuple[str, tuple[FrozenFluentError, ...]]:
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
- Duplicate Attributes: When message has duplicate attributes with same name, last attribute wins (per Fluent spec).

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

### `DEFAULT_MAX_EXPANSION_SIZE`

```python
DEFAULT_MAX_EXPANSION_SIZE: int = 1_000_000
```

| Attribute | Value |
|:----------|:------|
| Type | `int` |
| Value | 1,000,000 |
| Location | `ftllexengine.constants` |

- Purpose: Maximum total characters produced during message resolution. Prevents Billion Laughs attacks.
- Usage: Referenced by `ResolutionContext`, `FluentResolver`, `FluentBundle`.
- Import: `from ftllexengine.constants import DEFAULT_MAX_EXPANSION_SIZE`

---

### `MAX_CURRENCY_CACHE_SIZE`

```python
MAX_CURRENCY_CACHE_SIZE: int = 300
```

| Attribute | Value |
|:----------|:------|
| Type | `int` |
| Value | 300 |
| Location | `ftllexengine.constants` |

- Purpose: Maximum LRU cache entries for individual currency lookups.
- Usage: `_get_currency_impl` in `ftllexengine.introspection.iso`.
- Import: `from ftllexengine.constants import MAX_CURRENCY_CACHE_SIZE`

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

### `MAX_FORMAT_DIGITS`

```python
MAX_FORMAT_DIGITS: int = 20
```

| Attribute | Value |
|:----------|:------|
| Type | `int` |
| Value | 20 |
| Location | `ftllexengine.constants` |

- Purpose: Upper bound on `minimum_fraction_digits` and `maximum_fraction_digits` in `number_format()` and `currency_format()`.
- Usage: Values exceeding this limit are clamped to prevent excessive memory allocation during formatting.
- Security: Prevents DoS via pathological fraction digit requests.
- Import: `from ftllexengine.constants import MAX_FORMAT_DIGITS`

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
- Raises: `FrozenFluentError` (category=RESOLUTION) when depth limit exceeded.
- Behavior: `__enter__` validates limit BEFORE incrementing; prevents state corruption on exception.
- Import: `from ftllexengine.core.depth_guard import DepthGuard`

---

## `GlobalDepthGuard`

Global depth tracking across format_pattern calls using `contextvars`.

### Signature
```python
class GlobalDepthGuard:
    __slots__ = ("_max_depth", "_token")

    def __init__(self, max_depth: int = MAX_DEPTH) -> None: ...
    def __enter__(self) -> GlobalDepthGuard: ...
    def __exit__(self, exc_type, exc_val, exc_tb) -> None: ...
```

### Parameters
| Field | Type | Description |
|:------|:-----|:------------|
| `max_depth` | `int` | Maximum allowed global depth (default: MAX_DEPTH=100). |

### Constraints
- Thread: Safe (uses `contextvars.ContextVar` for async-safe per-task state).
- Purpose: Prevents depth limit bypass via custom function callbacks.
- Security: Custom functions calling `bundle.format_pattern()` cannot bypass limits.
- Raises: `FrozenFluentError` (category=RESOLUTION) when global depth limit exceeded.
- Internal: Used automatically by `FluentResolver.resolve_message()`.

---

## `RWLock`

Readers-writer lock with writer preference for high-concurrency FluentBundle access.

### Signature
```python
class RWLock:
    def __init__(self) -> None: ...
    def read(self, timeout: float | None = None) -> Generator[None, None, None]: ...
    def write(self, timeout: float | None = None) -> Generator[None, None, None]: ...
```

### Constraints
- Return: RWLock instance.
- State: Tracks active readers, active writer (as `int` thread identity), waiting writers, reader thread counts, writer reentry count, writer-held reads.
- Thread: Safe for all operations. Reentrant for both readers and writers (same thread can reacquire locks multiple times).
- Purpose: Allows multiple concurrent readers OR single exclusive writer.
- Timeout: Optional `timeout` parameter on `read()` and `write()`. `None` (default) waits indefinitely; `0.0` is non-blocking; positive float is deadline in seconds. Raises `TimeoutError` on expiry, `ValueError` if negative.
- Writer Preference: Writers are prioritized when waiting to prevent reader starvation.
- Lock Downgrading: Write-to-read downgrade supported. A thread holding the write lock can acquire read locks without blocking. When the write lock is released, held read locks convert to regular reader locks.
- Upgrade Limitation: Read-to-write lock upgrades are prohibited. Thread holding read lock cannot acquire write lock (raises RuntimeError).
- Usage: FluentBundle uses RWLock internally for concurrent format operations.
- Import: `from ftllexengine.runtime.rwlock import RWLock`
---

## `RWLock.read`

Context manager acquiring read lock for shared access.

### Signature
```python
@contextmanager
def read(self, timeout: float | None = None) -> Generator[None, None, None]:
```

### Parameters
| Parameter | Type | Req | Semantics |
|:----------|:-----|:----|:----------|
| `timeout` | `float \| None` | N | Max seconds to wait. `None` = indefinite, `0.0` = non-blocking |

### Constraints
- Return: Context manager yielding None.
- State: Increments active readers count. Reentrant for same thread.
- Thread: Safe. Multiple threads can hold read locks concurrently.
- Blocks: When writer is active or writers are waiting (writer preference).
- Raises: `TimeoutError` if lock not acquired within timeout. `ValueError` if timeout negative.
- Usage: `with lock.read(): # read data` or `with lock.read(timeout=1.0): # bounded wait`

---

## `RWLock.write`

Context manager acquiring write lock for exclusive access.

### Signature
```python
@contextmanager
def write(self, timeout: float | None = None) -> Generator[None, None, None]:
```

### Parameters
| Parameter | Type | Req | Semantics |
|:----------|:-----|:----|:----------|
| `timeout` | `float \| None` | N | Max seconds to wait. `None` = indefinite, `0.0` = non-blocking |

### Constraints
- Return: Context manager yielding None.
- State: Sets active writer. Blocks all other readers and writers. Reentrant (same thread can acquire multiple times).
- Thread: Safe. Only one thread can hold write lock at a time.
- Blocks: Until all readers release their locks.
- Raises: `RuntimeError` if thread attempts read-to-write lock upgrade. `TimeoutError` if lock not acquired within timeout. `ValueError` if timeout negative.
- Usage: `with lock.write(): # modify data` or `with lock.write(timeout=2.0): # bounded wait`

---

## Analysis Functions

---

## `entry_dependency_set`

Function that builds a namespace-prefixed dependency frozenset from reference sets.

### Signature
```python
def entry_dependency_set(
    message_refs: frozenset[str],
    term_refs: frozenset[str],
) -> frozenset[str]:
```

### Parameters
| Parameter | Type | Req | Semantics |
|:----------|:-----|:----|:----------|
| `message_refs` | `frozenset[str]` | Y | Message IDs referenced by entry |
| `term_refs` | `frozenset[str]` | Y | Term IDs referenced by entry |

### Constraints
- Return: Frozenset of prefixed dependency keys (e.g., `frozenset({"msg:welcome", "term:brand"})`).
- Raises: Never.
- State: None (pure function).
- Thread: Safe.
- Namespace: `msg:` prefix for message refs, `term:` prefix for term refs. Prevents collisions between same-name messages and terms.
- Complexity: O(N) where N = total references.
- Import: `from ftllexengine.analysis import entry_dependency_set`

### Example
```python
deps = entry_dependency_set(frozenset({"greeting"}), frozenset({"brand"}))
# deps: frozenset({"msg:greeting", "term:brand"})
```

---

## `make_cycle_key`

Function that creates a canonical display string from a cycle path.

### Signature
```python
def make_cycle_key(cycle: Sequence[str]) -> str:
```

### Parameters
| Parameter | Type | Req | Semantics |
|:----------|:-----|:----|:----------|
| `cycle` | `Sequence[str]` | Y | Cycle path with closing repeat |

### Constraints
- Return: Canonical arrow-separated string (e.g., `"A -> B -> C -> A"`). Empty string for empty input.
- Raises: Never.
- State: None (pure function).
- Thread: Safe.
- Canonical: Rotates cycle to start with lexicographically smallest node. All rotations of the same cycle produce identical keys.
- Import: `from ftllexengine.analysis import make_cycle_key`

### Example
```python
key = make_cycle_key(["B", "C", "A", "B"])
# key: "A -> B -> C -> A"
```

---

## `detect_cycles`

Function that detects all cycles in a dependency graph using iterative DFS.

### Signature
```python
def detect_cycles(dependencies: Mapping[str, set[str]]) -> list[list[str]]:
```

### Parameters
| Parameter | Type | Req | Semantics |
|:----------|:-----|:----|:----------|
| `dependencies` | `Mapping[str, set[str]]` | Y | Node ID to set of referenced node IDs |

### Constraints
- Return: List of cycles where each cycle is a list of node IDs forming the cycle path (closed: last element repeats first). Empty list if no cycles detected. Cycles are deduplicated via canonical tuple form.
- Raises: Never.
- State: None (pure function).
- Thread: Safe.
- Algorithm: Iterative DFS with explicit stack. Prevents RecursionError on deep graphs (>1000 nodes in linear chain).
- Complexity: O(V + E) time, O(V) space where V = nodes, E = edges.
- Security: Uses iterative DFS to prevent stack overflow attacks via deeply nested dependency chains in untrusted FTL resources.
- Import: `from ftllexengine.analysis import detect_cycles`

### Example
```python
deps = {"a": {"b"}, "b": {"c"}, "c": {"a"}}
cycles = detect_cycles(deps)
# cycles: [['a', 'b', 'c', 'a']] (canonical rotation)
```

---

## `IntegrityCache`

Format result cache with cryptographic integrity verification for financial-grade applications.

### Signature
```python
class IntegrityCache:
    def __init__(
        self,
        maxsize: int = 1000,
        max_entry_weight: int = 10000,
        max_errors_per_entry: int = 50,
        *,
        write_once: bool = False,
        strict: bool = True,
        enable_audit: bool = False,
        max_audit_entries: int = 10000,
    ) -> None: ...
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `maxsize` | `int` | N | Maximum cache entries (LRU eviction). |
| `max_entry_weight` | `int` | N | Maximum memory weight per entry in approximate bytes. |
| `max_errors_per_entry` | `int` | N | Maximum errors stored per entry. |
| `write_once` | `bool` | N | Reject updates to existing keys (data race prevention). |
| `strict` | `bool` | N | Raise on corruption/write conflicts. Sourced from `CacheConfig.integrity_strict`. |
| `enable_audit` | `bool` | N | Maintain operation history for compliance. |
| `max_audit_entries` | `int` | N | Maximum audit log entries before oldest eviction. |

### Constraints
- Return: IntegrityCache instance.
- State: Mutable cache with integrity verification.
- Thread: Safe (internal locking).
- Integrity: Each entry has BLAKE2b-128 checksum computed at creation and verified on retrieval.
- Corruption: Corrupted entries are evicted silently (strict=False) or raise CacheCorruptionError (strict=True).
- Key Normalization: Cache keys are normalized to prevent hash collisions between values that format differently:
  - NaN: `Decimal("NaN")` normalized to `"__NaN__"` (IEEE 754 NaN != NaN; prevents unretrievable cache entries).
  - Decimal: Uses `str(value)` to preserve scale (`Decimal("1.0")` vs `Decimal("1.00")` are distinct for CLDR plural rules).
  - Datetime: Includes isoformat and tzinfo string; same-UTC-instant different-timezone datetimes produce distinct keys.
  - Collections: Supports Sequence/Mapping ABCs (UserList, ChainMap) in addition to list/tuple/dict.
- Idempotent Writes: When `write_once=True`, concurrent writes with identical content are treated as idempotent success (not conflict). Content comparison uses `IntegrityCacheEntry.content_hash` which excludes metadata (created_at, sequence).
- Import: `from ftllexengine.runtime.cache import IntegrityCache`
- Independence: `strict` controls cache corruption response independently of `FluentBundle.strict` (formatting behavior). Sourced from `CacheConfig.integrity_strict`.
- Access: Typically accessed via FluentBundle cache parameters, not directly constructed.

---

## `IntegrityCache.get`

Retrieve cached format result with integrity verification.

### Signature
```python
def get(
    self,
    message_id: str,
    args: Mapping[str, FluentValue] | None,
    attribute: str | None,
    locale_code: str,
    use_isolating: bool,
) -> IntegrityCacheEntry | None:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `message_id` | `str` | Y | Message identifier. |
| `args` | `Mapping[str, FluentValue] \| None` | Y | Message arguments (may contain unhashable values). |
| `attribute` | `str \| None` | Y | Attribute name. |
| `locale_code` | `str` | Y | Locale code. |
| `use_isolating` | `bool` | Y | Whether Unicode isolation marks are used. |

### Constraints
- Return: IntegrityCacheEntry if found and valid, None otherwise.
- Raises: `CacheCorruptionError` if strict=True and entry fails verification.
- State: Read (may evict corrupted entries).
- Thread: Safe.

---

## `IntegrityCache.put`

Store format result with integrity checksum.

### Signature
```python
def put(
    self,
    message_id: str,
    args: Mapping[str, FluentValue] | None,
    attribute: str | None,
    locale_code: str,
    use_isolating: bool,
    formatted: str,
    errors: tuple[FrozenFluentError, ...],
) -> None:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `message_id` | `str` | Y | Message identifier. |
| `args` | `Mapping[str, FluentValue] \| None` | Y | Message arguments (may contain unhashable values). |
| `attribute` | `str \| None` | Y | Attribute name. |
| `locale_code` | `str` | Y | Locale code. |
| `use_isolating` | `bool` | Y | Whether Unicode isolation marks are used. |
| `formatted` | `str` | Y | Formatted message result. |
| `errors` | `tuple[FrozenFluentError, ...]` | Y | Frozen errors from resolution. |

### Constraints
- Return: None.
- Raises: `WriteConflictError` if write_once=True and strict=True and key exists with different content.
- Idempotent: When write_once=True, identical content (same formatted+errors) silently succeeds without error (thundering herd safe).
- State: Mutates cache.
- Thread: Safe.
- Skip: Entry not stored if weight exceeds max_entry_weight or error count exceeds max_errors_per_entry.

---

## `IntegrityCache.get_stats`

Get cache statistics including security parameters.

### Signature
```python
def get_stats(self) -> dict[str, int | float | bool]:
```

### Constraints
- Return: Dict with keys: size, maxsize, hits, misses, hit_rate, unhashable_skips, oversize_skips, error_bloat_skips, corruption_detected, idempotent_writes, sequence, max_entry_weight, max_errors_per_entry, write_once, strict, audit_enabled, audit_entries.
- State: Read-only.
- Thread: Safe.

---

## `IntegrityCache.idempotent_writes`

Property returning count of benign concurrent writes with identical content.

### Signature
```python
@property
def idempotent_writes(self) -> int:
```

### Constraints
- Return: Number of writes detected as idempotent (identical content already cached).
- State: Read-only.
- Thread: Safe.
- Counter: Reset to 0 when cache is cleared.

---

## `IntegrityCacheEntry`

Immutable cache entry with cryptographic integrity metadata.

### Signature
```python
@dataclass(frozen=True, slots=True)
class IntegrityCacheEntry:
    formatted: str
    errors: tuple[FrozenFluentError, ...]
    checksum: bytes
    created_at: float
    sequence: int
```

### Constraints
- Return: Frozen dataclass instance.
- Immutable: All fields are read-only after creation.
- Checksum: BLAKE2b-128 hash of all fields (content + metadata) for complete audit trail integrity.
- Import: `from ftllexengine.runtime.cache import IntegrityCacheEntry`

---

## `IntegrityCacheEntry.content_hash`

Property returning content-only hash for idempotent write detection.

### Signature
```python
@property
def content_hash(self) -> bytes:
```

### Constraints
- Return: 16-byte BLAKE2b digest of (formatted, errors) only.
- Excludes: Does NOT include metadata (created_at, sequence).
- Purpose: Two entries with identical content have identical content_hash regardless of when they were created.
- Usage: Used by IntegrityCache.put() for idempotent write detection in thundering herd scenarios.

---

## `IntegrityCacheEntry.verify`

Method to verify entry integrity.

### Signature
```python
def verify(self) -> bool:
```

### Constraints
- Return: True if checksum matches recomputed value AND all errors verify, False otherwise.
- Thread: Safe (read-only).
- Recursive: Verifies each FrozenFluentError's integrity if verify_integrity() method available.

---

## `WriteLogEntry`

Immutable audit log entry for cache operations.

### Signature
```python
@dataclass(frozen=True, slots=True)
class WriteLogEntry:
    operation: str
    key_hash: str
    timestamp: float
    sequence: int
    checksum_hex: str
```

### Parameters
| Field | Type | Description |
|:------|:-----|:------------|
| `operation` | `str` | Operation type (GET, PUT, HIT, MISS, EVICT, CORRUPTION). |
| `key_hash` | `str` | BLAKE2b hash of cache key (privacy-preserving). |
| `timestamp` | `float` | Monotonic timestamp of operation. |
| `sequence` | `int` | Cache entry sequence number (for PUT operations). |
| `checksum_hex` | `str` | Hex representation of entry checksum (for tracing). |

### Constraints
- Immutable: Frozen dataclass with slots.
- Purpose: Post-mortem analysis and debugging when audit logging enabled.
- Import: `from ftllexengine.runtime.cache import WriteLogEntry`

---

## `IntegrityCache.get_audit_log`

Get audit log entries.

### Signature
```python
def get_audit_log(self) -> tuple[WriteLogEntry, ...]:
```

### Constraints
- Return: Tuple of WriteLogEntry instances (empty if audit disabled).
- State: Read-only.
- Thread: Safe.

---

## `IntegrityCache.clear`

Clear all cached entries. Observability metrics are preserved.

### Signature
```python
def clear(self) -> None:
```

### Constraints
- Return: None.
- State: Removes all cached entries from the LRU store. All counters (hits, misses, unhashable_skips, oversize_skips, error_bloat_skips, corruption_detected, idempotent_writes) and sequence number accumulate across `clear()` calls; they are never reset. Audit log is NOT cleared (historical record).
- Thread: Safe.
- Usage: Called automatically by FluentBundle on `add_resource()` or `add_function()`.

---
